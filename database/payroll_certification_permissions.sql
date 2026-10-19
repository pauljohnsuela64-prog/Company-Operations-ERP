-- Explicit catalog registration only. No production role grants or startup execution.
INSERT INTO permissions(permission_code,description)
SELECT 'payroll.certification.certify','Publish verified payroll cutoff certifications'
WHERE NOT EXISTS(SELECT 1 FROM permissions WHERE permission_code='payroll.certification.certify');
INSERT INTO permissions(permission_code,description)
SELECT 'payroll.certification.revoke','Revoke payroll cutoff certifications'
WHERE NOT EXISTS(SELECT 1 FROM permissions WHERE permission_code='payroll.certification.revoke');
