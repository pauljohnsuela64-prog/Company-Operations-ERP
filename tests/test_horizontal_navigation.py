from security_helpers import user_state, stamp_session
"""Render navigation without invoking business routes or connecting to a database."""

from contextlib import ExitStack
from html.parser import HTMLParser
import importlib
import os
import unittest
from unittest.mock import patch

from flask import render_template_string, session, g


class NavigationHTML(HTMLParser):
    def __init__(self, html):
        super().__init__()
        self.in_navigation = False
        self.links = []
        self.groups = {}
        self.summaries = []
        self.in_breadcrumb = False
        self.breadcrumbs = []
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "nav" and attrs.get("id") == "erp-navigation":
            self.in_navigation = True
        if tag == "nav" and attrs.get("aria-label") == "Breadcrumb":
            self.in_breadcrumb = True
        if self.in_navigation and tag == "a":
            self.links.append(attrs)
        if self.in_navigation and tag == "details":
            self.groups[attrs["id"]] = attrs
        if self.in_navigation and tag == "summary":
            self.summaries.append(attrs)

    def handle_endtag(self, tag):
        if tag == "nav":
            self.in_navigation = False
            self.in_breadcrumb = False

    def handle_data(self, data):
        if self.in_breadcrumb and data.strip():
            self.breadcrumbs.append(data.strip())


PERMISSIONS = {
    "employees.view", "departments.view", "attendance.view", "leave.view", "payroll.view",
    "inventory.view", "procurement.view", "it_assets.view", "helpdesk.view", "finance.view",
    "users.manage", "roles.manage", "audit_logs.view",
}


class HorizontalNavigationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.stack = ExitStack()
        cls.addClassCleanup(cls.stack.close)
        cls.stack.enter_context(patch("dotenv.load_dotenv", return_value=False))
        cls.stack.enter_context(patch.dict(os.environ, {"SECRET_KEY": "isolated-navigation-tests", "ERP_ENV": "testing", "ERP_DEBUG": "false"}))
        cls.stack.enter_context(patch("mysql.connector.connect", side_effect=AssertionError("No database access allowed")))
        cls.erp = importlib.import_module("app")

    def render(self, path="/dashboard", permissions=PERMISSIONS):
        with self.erp.app.test_request_context(path):
            state = user_state(username="navigation.tester", permissions=permissions)
            stamp_session(self.erp.app, session, state)
            g.authorization = state
            html = render_template_string('{% extends "base.html" %}{% block title %}Current page title{% endblock %}')
            return html, NavigationHTML(html)

    def test_all_existing_destinations_appear_once_and_resolve(self):
        html, nav = self.render()
        self.assertEqual(len(nav.links), 25)
        hrefs = [a["href"] for a in nav.links]
        self.assertEqual(len(hrefs), len(set(hrefs)), "Duplicate navigation destination")
        adapter = self.erp.app.url_map.bind("localhost")
        for href in hrefs:
            with self.subTest(href=href):
                endpoint, _ = adapter.match(href, method="GET")
                self.assertIn(endpoint, self.erp.app.view_functions)
        self.assertEqual(set(nav.groups), {"nav-hr", "nav-inventory", "nav-procurement", "nav-it", "nav-finance", "nav-admin"})
        self.assertIn('aria-label="Breadcrumb"', html)
        self.assertIn("Current page title", html)
        self.assertEqual(len(nav.summaries), 6)
        for attrs in nav.summaries:
            self.assertIn(f'id="{attrs["aria-controls"]}"', html)
        self.assertTrue(all(attrs.get("name") == "erp-modules" for attrs in nav.groups.values()))

    def test_existing_permission_visibility_is_preserved(self):
        combinations = [set(), PERMISSIONS]
        combinations.extend({p} for p in PERMISSIONS)
        combinations.extend(PERMISSIONS - {p} for p in PERMISSIONS)
        combinations.extend({admin, "attendance.view", "leave.view"} for admin in ("users.manage", "roles.manage", "audit_logs.view"))
        combinations.append({"inventory.view", "procurement.view"})
        for permissions in combinations:
            with self.subTest(permissions=sorted(permissions)):
                _, nav = self.render(permissions=permissions)
                actual = {link["href"] for link in nav.links}
                expected = {"/dashboard"}
                for permission, paths in {
                    "employees.view": ["/employees"], "departments.view": ["/departments"],
                    "payroll.view": ["/payroll/compensation"],
                    "inventory.view": ["/inventory/categories", "/inventory/warehouses", "/inventory/items", "/inventory/stock", "/inventory/stock/movements"],
                    "it_assets.view": ["/it/assets"], "helpdesk.view": ["/it/help-desk"],
                    "finance.view": ["/finance", "/finance/expenses", "/finance/expense-categories", "/finance/reports", "/finance/budgets"],
                    "users.manage": ["/admin/users"], "roles.manage": ["/admin/roles"], "audit_logs.view": ["/admin/audit-logs"],
                }.items():
                    if permission in permissions:
                        expected.update(paths)
                if {"inventory.view", "procurement.view"} <= permissions:
                    expected.update({"/procurement/suppliers", "/procurement/requests", "/procurement/orders", "/procurement/receipts"})
                if permissions & {"users.manage", "roles.manage", "audit_logs.view"}:
                    if "attendance.view" in permissions:
                        expected.add("/attendance")
                    if "leave.view" in permissions:
                        expected.add("/leave/requests")
                self.assertEqual(actual, expected)
                self.assertEqual(len(nav.links), len(expected))

    def test_nested_pages_select_one_link_and_highlight_correct_module(self):
        examples = [
            ("/employees/42/edit", "/employees", "hr"),
            ("/departments/add", "/departments", "hr"),
            ("/attendance/42/edit", "/attendance", "hr"),
            ("/leave/types/42/edit", "/leave/requests", "hr"),
            ("/leave/balances", "/leave/requests", "hr"),
            ("/payroll/periods/42", "/payroll/compensation", "hr"),
            ("/payroll/entries/42/payslip", "/payroll/compensation", "hr"),
            ("/inventory/stock/movements", "/inventory/stock/movements", "inventory"),
            ("/inventory/stock/out", "/inventory/stock", "inventory"),
            ("/procurement/requests/42/items/add", "/procurement/requests", "procurement"),
            ("/procurement/orders/42", "/procurement/orders", "procurement"),
            ("/procurement/receipts/history/42", "/procurement/receipts", "procurement"),
            ("/it/assets/categories/42/edit", "/it/assets", "it"),
            ("/it/help-desk/42", "/it/help-desk", "it"),
            ("/finance", "/finance", "finance"),
            ("/finance/expenses/42", "/finance/expenses", "finance"),
            ("/finance/expense-categories/42/edit", "/finance/expense-categories", "finance"),
            ("/finance/reports", "/finance/reports", "finance"),
            ("/finance/budgets/42", "/finance/budgets", "finance"),
            ("/admin/users/42/reset-password", "/admin/users", "admin"),
            ("/admin/roles/42/permissions", "/admin/roles", "admin"),
            ("/admin/audit-logs?module=PAYROLL", "/admin/audit-logs", "admin"),
        ]
        for path, href, group in examples:
            with self.subTest(path=path):
                _, nav = self.render(path)
                active = [a for a in nav.links if a.get("aria-current") == "page"]
                self.assertEqual([a["href"] for a in active], [href])
                self.assertIn("is-active", active[0]["class"])
                self.assertEqual([key for key, attrs in nav.groups.items() if "is-active" in attrs.get("class", "")], [f"nav-{group}"])
                self.assertFalse(any("open" in attrs for attrs in nav.groups.values()))

    def test_every_get_route_has_one_active_navigation_destination(self):
        for rule in self.erp.app.url_map.iter_rules():
            if "GET" not in rule.methods or rule.endpoint in {"static", "index", "login", "logout"}:
                continue
            path = rule.rule
            for argument in rule.arguments:
                path = path.replace(f"<int:{argument}>", "42")
            with self.subTest(endpoint=rule.endpoint):
                _, nav = self.render(path)
                self.assertEqual(len([a for a in nav.links if a.get("aria-current") == "page"]), 1)

    def test_empty_groups_are_hidden_and_dashboard_stays_standalone(self):
        _, nav = self.render(permissions=set())
        self.assertEqual(nav.groups, {})
        self.assertEqual([a["href"] for a in nav.links], ["/dashboard"])
        self.assertEqual(nav.links[0]["aria-current"], "page")

    def test_account_breadcrumbs_and_obsolete_sidebar_removal(self):
        html, nav = self.render('/admin/roles/42/permissions')
        self.assertEqual(nav.breadcrumbs, ['Home', '/', 'Administration', '/', 'Roles & Permissions', '/', 'Current page title'])
        self.assertIn('navigation.tester', html)
        self.assertIn('Test role', html)
        self.assertIn('href="/logout"', html)
        self.assertIn('Administration', html)
        self.assertIn('Roles &amp; Permissions', html)
        self.assertIn('aria-controls="erp-navigation"', html)
        self.assertIn('js/navigation.js', html)
        self.assertNotIn('sidebar', html)
        self.assertNotIn('compact-toggle', html)

    def test_template_syntax_for_all_existing_pages(self):
        for template in self.erp.app.jinja_env.list_templates():
            with self.subTest(template=template):
                self.erp.app.jinja_env.get_template(template)


if __name__ == "__main__":
    unittest.main()
