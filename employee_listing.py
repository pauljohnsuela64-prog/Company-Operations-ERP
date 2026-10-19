"""Bounded listing inputs, independent of Employee write/lifecycle validation."""
import re


class EmployeeListingInputError(ValueError):
    pass


def listing_inputs(search='',page=1,page_size=25):
    if not isinstance(search,str):raise EmployeeListingInputError('Search must be text.')
    search=search.strip()
    if len(search)>100:raise EmployeeListingInputError('Search must not exceed 100 characters.')
    try:search.encode('utf-8')
    except UnicodeError:raise EmployeeListingInputError('Search must be valid Unicode.') from None
    if any(ord(c)<32 or ord(c)==127 for c in search):
        raise EmployeeListingInputError('Search must not contain control characters.')
    values=[]
    for value,label,maximum in ((page,'Page',2147483647),(page_size,'Page size',100)):
        raw=str(value)
        if isinstance(value,bool) or not re.fullmatch(r'[0-9]{1,10}',raw) or not 1<=int(raw)<=maximum:
            raise EmployeeListingInputError(f'{label} must be a positive integer up to {maximum}.')
        values.append(int(raw))
    return search,*values


def listing_query_args(args):
    fields={'search':'','page':'1','page_size':'25'}
    if any(len(args.getlist(field))>1 for field in fields):
        raise EmployeeListingInputError('Submit only one value for each listing parameter.')
    return listing_inputs(*(args.get(field,default) for field,default in fields.items()))


def literal_prefix(search):
    return search.replace('!','!!').replace('%','!%').replace('_','!_')+'%'
