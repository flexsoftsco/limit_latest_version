$(document).on('toolbar_setup',function(){
  // v13 link
  $('div.dropdown-menu-right#toolbar-user').append('<div class="dropdown-divider"></div><a class="dropdown-item" href="/app/usage-info">           Usage Info          </a>')

  // v12 link
  $('ul#toolbar-user').append('<li class="divider"></li><li><a href="/desk#usage-info">       Usage Info</a></li>')
});
$(document).ready(function() {
  frappe.call({
		method: "limit.limits.get_warning_for_expiry",
		callback: function(r) {
			var message = r.message;
			if (message) {
        msgprint(message);
			}
    }
  });
});