from __future__ import unicode_literals
import frappe
from frappe import _
from frappe.utils import now_datetime, getdate, flt, cint, get_fullname
from frappe.installer import update_site_config
from frappe.utils.data import formatdate
from frappe.utils.user import get_enabled_system_users

from frappe.utils.__init__ import get_site_info
import os, subprocess, json
from six.moves.urllib.parse import parse_qsl, urlsplit, urlunsplit, urlencode
from six import string_types
from frappe.handler import logout

from limit.utils.user import disable_users
# from frappe.auth import LoginManager

class SiteExpiredError(frappe.ValidationError):
	http_status_code = 417

EXPIRY_WARNING_DAYS = 15

@frappe.whitelist()
def get_warning_for_expiry():
	### warn user if expriy equals  EXPIRY_WARNING_DAYS or less
	message = ''
	expires_on = get_expiry()
	if expires_on :
		today = now_datetime().date()
		days_to_expiry = (expires_on - today).days
		if days_to_expiry <= EXPIRY_WARNING_DAYS and days_to_expiry >= 0 :
			message = get_user_expiry_message (waringing=1,days_to_expire=days_to_expiry)
	return message

def check_if_expired():
	print('check_if_expired',has_expired())

	"""check if account is expired. If expired, do not allow login"""
	if not has_expired():
		return
	message = get_user_expiry_message ()
	if message :
		frappe.throw(msg=message,title='Subscription Expired', exc=SiteExpiredError)
		logout()


def get_expiry():
	expire_date = None
	expires_on = get_limits().expiry
	if expires_on :
		expire_date = getdate(expires_on)
	return expire_date	

def has_expired():
	user = (frappe.form_dict and frappe.form_dict.get("usr") or "").lower()
	if frappe.session.user=="Administrator"  or user=='administrator' :
		return False

	expires_on = get_limits().expiry
	print('expires_on',expires_on)
	if not expires_on:
		return False
	if now_datetime().date() <= getdate(expires_on):
		return False

	return True

def get_user_expiry_message(waringing=0, days_to_expire=0):
	message = ''
	limits = get_limits()
	if not limits.expiry:
		return message
	expires_on = formatdate(limits.get("expiry"))
	support_email = limits.get("support_email")
	support_phone = limits.get("support_phone")
	bank_name = limits.get("bank_name")
	subscription_fees = limits.get("subscription_fees")
	beneficiary = limits.get("beneficiary")
	IBAN = limits.get("iban")
	expire_info =  f'will expire After {days_to_expire} days' if waringing else f'has expired on {expires_on}'
	if support_email :
		message += _(f"Your subscription for {frappe.local.site} {expire_info}. <br>To renew, Email us : <b>{support_email}</b>")

	if support_phone:
		message += _(""" or <br>Contact us : <b>{0}</b>""").format(support_phone)

	if bank_name:
		message += _("""<br>Bank Name : <b>{0}</b>""").format(bank_name)

	if subscription_fees:
		message += _(""" <br>Subscription fees : <b>{0}</b>""").format(subscription_fees)

	if beneficiary:
		message += _(""" <br>Beneficiary : <b>{0}</b>""").format(beneficiary)
	
	if IBAN:
		message += _(""" <br>IBAN : <b>{0}</b>""").format(IBAN)

	return message

def get_expiry_message():
	if "System Manager" not in frappe.get_roles():
		return ""

	limits = get_limits()
	if not limits.expiry:
		return ""

	expires_on = getdate(get_limits().get("expiry"))
	today = now_datetime().date()

	message = ""
	if today > expires_on:
		message = _("Your subscription has expired.")
	else:
		days_to_expiry = (expires_on - today).days

		if days_to_expiry == 0:
			message = _("Your subscription will expire today.")

		elif days_to_expiry == 1:
			message = _("Your subscription will expire tomorrow.")

		elif days_to_expiry <= EXPIRY_WARNING_DAYS:
			message = _("Your subscription will expire on {0}.").format(formatdate(expires_on))

	if message and limits.support_email:
		# upgrade_link = get_upgrade_link(limits.upgrade_url)
		message += ' ' + _('To renew, email {0} or contact {1}').format(limits.support_email,limits.support_phone)

	return message

@frappe.whitelist()
def get_usage_info():
	'''Get data to show for Usage Info'''
	# imported here to prevent circular import
	from frappe.email.queue import get_emails_sent_this_month

	limits = get_limits()
	if not (limits and any([limits.users, limits.space, limits.emails, limits.expiry])):
		# no limits!
		return

	limits.space = (limits.space or 0) * 1024.0 # to MB
	if not limits.space_usage:
		# hack! to show some progress
		limits.space_usage = {
			'database_size': 26,
			'files_size': 1,
			'backup_size': 1,
			'total': 28
		}

	usage_info = frappe._dict({
		'limits': limits,
		'enabled_users': len(get_enabled_system_users()),
		'emails_sent': get_emails_sent_this_month(),
		'space_usage': limits.space_usage['total'],
	})

	if limits.expiry:
		usage_info['expires_on'] = formatdate(limits.expiry)
		usage_info['days_to_expiry'] = (getdate(limits.expiry) - getdate()).days

	# if limits.upgrade_url:
	# 	usage_info['upgrade_url'] = get_upgrade_url(limits.upgrade_url)

	return usage_info

def get_upgrade_url(upgrade_url):
	parts = urlsplit(upgrade_url)
	params = dict(parse_qsl(parts.query))
	params.update({
		'site': frappe.local.site,
		'email': frappe.session.user,
		'full_name': get_fullname(),
		'country': frappe.db.get_value("System Settings", "System Settings", 'country')
	})

	query = urlencode(params, doseq=True)
	url = urlunsplit((parts.scheme, parts.netloc, parts.path, query, parts.fragment))

	return url

def get_upgrade_link(upgrade_url, label=None):
	upgrade_url = get_upgrade_url(upgrade_url)
	upgrade_link = '<a href="{upgrade_url}" target="_blank">{click_here}</a>'.format(upgrade_url=upgrade_url, click_here=label or _('click here'))
	return upgrade_link

def get_limits():
	'''
		"limits": {
			"users": 1,
			"space": 0.5, # in GB
			"emails": 1000 # per month
			"expiry": "2099-12-31"
		}
	'''
	return frappe._dict(frappe.local.conf.limits or {})

def update_limits(limits_dict):
	'''Add/Update limit in site_config'''
	limits = get_limits()
	limits.update(limits_dict)
	update_site_config("limits", limits, validate=False)
	disable_users(limits)
	frappe.local.conf.limits = limits

def clear_limit(key):
	'''Remove a limit option from site_config'''
	limits = get_limits()
	to_clear = [key] if isinstance(key, string_types) else key
	for key in to_clear:
		if key in limits:
			del limits[key]

	update_site_config("limits", limits, validate=False)
	frappe.conf.limits = limits

def validate_space_limit(file_size):
	"""Stop from writing file if max space limit is reached"""
	from frappe.utils.file_manager import MaxFileSizeReachedError

	limits = get_limits()
	if not limits.space:
		return

	# to MB
	space_limit = flt(limits.space * 1024.0, 2)

	# in MB
	usage = frappe._dict(limits.space_usage or {})
	if not usage:
		# first time
		usage = frappe._dict(update_space_usage())

	file_size = file_size / (1024.0 ** 2)

	if flt(flt(usage.total) + file_size, 2) > space_limit:
		# Stop from attaching file
		# frappe.throw(_("You have exceeded the max space of {0} for your plan. {1}.").format(
		# 	"<b>{0}MB</b>".format(cint(space_limit)) if (space_limit < 1024) else "<b>{0}GB</b>".format(limits.space),
		# 	'<a href="https://flexsofts.com/contact">{0}</a>'.format(_("Click here to contact us."))),
		# 	MaxFileSizeReachedError)
		message =_("You have exceeded the max space of {0} for your plan. {1}.").format(
		"<b>{0}MB</b>".format(cint(space_limit)) if (space_limit < 1024) else "<b>{0}GB</b>".format(limits.space),
		'Contact us on email <b>{0}</b> or phone <b>{1}</b>'.format(limits.support_email,limits.support_phone))
		frappe.throw(msg=message,title='Space Usage Limit Reached', exc=MaxFileSizeReachedError)
	# update files size in frappe subscription
	usage.files_size = flt(usage.files_size) + file_size
	update_limits({ 'space_usage': usage })

def update_space_usage():
	# public and private files
	files_size = get_folder_size(frappe.get_site_path("public", "files"))
	files_size += get_folder_size(frappe.get_site_path("private", "files"))

	backup_size = get_folder_size(frappe.get_site_path("private", "backups"))
	database_size = get_database_size()

	usage = {
		'files_size': flt(files_size, 2),
		'backup_size': flt(backup_size, 2),
		'database_size': flt(database_size, 2),
		'total': flt(flt(files_size) + flt(backup_size) + flt(database_size), 2)
	}

	update_limits({ 'space_usage': usage })

	return usage

def get_folder_size(path):
	'''Returns folder size in MB if it exists'''
	if os.path.exists(path):
		return flt(subprocess.check_output(['du', '-ms', path]).split()[0], 2)

def get_database_size():
	'''Returns approximate database size in MB'''
	db_name = frappe.conf.db_name

	# This query will get the database size in MB
	db_size = frappe.db.sql('''
		SELECT table_schema "database_name", sum( data_length + index_length ) / 1024 / 1024 "database_size"
		FROM information_schema.TABLES WHERE table_schema = %s GROUP BY table_schema''', db_name, as_dict=True)

	return flt(db_size[0].get('database_size'), 2)

def update_site_usage():
	data = get_site_info()
	# exists = os.path.isfile(frappe.get_site_path("site_data.json"))
	with open(os.path.join(frappe.get_site_path(), 'site_data.json'), 'w') as outfile:
		json.dump(data, outfile)
		outfile.close()
