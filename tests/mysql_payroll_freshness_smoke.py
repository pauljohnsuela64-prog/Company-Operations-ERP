"""CI entry point for the fifteen original Payroll freshness scenarios."""
import mysql_payroll_freshness_investigation as regression

if __name__ == '__main__':
    regression.audit.harness.run = regression.run
    regression.audit.harness.main()
