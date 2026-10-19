"""Employee listing bounds, route authorization and SQL/query structure."""
import unittest
from unittest.mock import MagicMock,patch
from werkzeug.datastructures import MultiDict
import test_hr_validation as fixtures
from employee_listing import listing_inputs,listing_query_args,literal_prefix,EmployeeListingInputError
from employee_repository import get_employee_page


class ListingInputTests(unittest.TestCase):
    def test_defaults_trim_unicode_literal_patterns(self):
        self.assertEqual(listing_query_args(MultiDict()),('',1,25))
        self.assertEqual(listing_inputs('  José_%!  ','2','100'),('José_%!',2,100))
        self.assertEqual(literal_prefix('A!_%'),'A!!!_!%%')
        self.assertEqual(listing_inputs(' '*1000),('',1,25))
        self.assertEqual(len(listing_inputs('x'*100)[0]),100)

    def test_invalid_bounds_and_duplicate_parameters(self):
        for page in ('','0','-1','1.0','a','1e2','9'*1000,2147483648,True):
            with self.subTest(page=str(page)[:30]),self.assertRaises(EmployeeListingInputError):listing_inputs(page=page)
        for size in ('',0,-1,101,'NaN','9'*1000,False):
            with self.assertRaises(EmployeeListingInputError):listing_inputs(page_size=size)
        for search in ('x'*101,'A\x00B','A\nB','\ud800',None):
            with self.assertRaises(EmployeeListingInputError):listing_inputs(search)
        for field in ('search','page','page_size'):
            with self.assertRaises(EmployeeListingInputError):listing_query_args(MultiDict([(field,'1'),(field,'2')]))

    def test_parameterized_consistent_conditions_bound_rows_and_cleanup(self):
        db=MagicMock();cur=db.cursor.return_value
        cur.fetchone.return_value={'total':51};cur.fetchall.return_value=[]
        with patch('employee_repository.get_connection',return_value=db):
            result=get_employee_page("O'_%!",999,25)
        count,data=cur.execute.call_args_list
        self.assertNotIn("O'",data.args[0]);self.assertIn("ESCAPE '!'",data.args[0])
        self.assertEqual(count.args[0].split(' WHERE ')[1],data.args[0].split(' WHERE ')[1].split(' ORDER BY ')[0])
        self.assertEqual(data.args[1],(*count.args[1],25,50))
        self.assertIn('e.last_name,e.first_name,e.employee_id',data.args[0])
        self.assertEqual((result['page'],result['pages'],result['total']),(3,3,51))
        db.start_transaction.assert_called_once_with(isolation_level='REPEATABLE READ',readonly=True,consistent_snapshot=True)
        db.commit.assert_not_called();db.rollback.assert_called_once();db.close.assert_called_once()


class ListingRouteTests(unittest.TestCase):
    setUpClass=classmethod(fixtures.HRRouteTests.setUpClass.__func__)
    setUp=fixtures.HRRouteTests.setUp

    def test_listing_escaping_buttons_and_retained_navigation(self):
        result=dict(employees=[dict(self.employee,first_name='<script>alert(1)</script>')],
                    search='A_% & <b>',page=2,page_size=25,total=51,pages=3)
        with patch.object(self.erp,'get_employee_page',return_value=result) as query:
            response=self.client.get('/employees?search=A_%25+%26+%3Cb%3E&page=2')
        self.assertEqual(response.status_code,200);query.assert_called_once_with('A_% & <b>',2,25)
        html=response.get_data(as_text=True)
        self.assertIn('&lt;script&gt;',html);self.assertNotIn('<script>alert',html)
        self.assertIn('A_% &amp; &lt;b&gt;',html)
        self.assertIn('rel="next"',html);self.assertIn('rel="prev"',html)
        self.assertIn('page=3',html);self.assertIn('page=1',html)
        self.assertIn('51 matching employees',html)
        self.assertIn('/employees/add',html);self.assertIn('/employees/1/edit',html)
        # The search form has no page field, so a new search begins on page 1.
        self.assertNotIn('name="page"',html)

    def test_invalid_requests_do_not_query(self):
        with patch.object(self.erp,'get_employee_page') as query:
            for suffix in ('?page=-1','?page=0','?page=no','?page='+'9'*1000,
                           '?page_size=101','?search='+'x'*101,'?page=1&page=2'):
                response=self.client.get('/employees'+suffix)
                self.assertEqual(response.status_code,400)
                self.assertNotIn('matching employees',response.get_data(as_text=True))
            query.assert_not_called()

    def test_view_only_revoked_disabled_and_anonymous(self):
        result=dict(employees=[self.employee],search='',page=1,page_size=25,total=1,pages=1)
        with patch.object(self.erp,'get_employee_page',return_value=result) as query:
            self.state['permissions']=frozenset(['employees.view'])
            html=self.client.get('/employees').get_data(as_text=True)
            self.assertNotIn('/employees/add',html);self.assertNotIn('/employees/1/edit',html)
            self.state['permissions']=frozenset()
            self.assertTrue(self.client.get('/employees?search=secret').location.endswith('/dashboard'))
            self.state['is_active']=False
            self.assertTrue(self.client.get('/employees').location.endswith('/login'))
            self.assertTrue(self.client.get('/employees').location.endswith('/login'))
            self.assertEqual(query.call_count,1)


if __name__=='__main__':unittest.main()
