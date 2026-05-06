package access.authorization.user.validate.utils.policy_0465

# Auto-generated policy 465 (Rego v1 syntax)
# Package: access.authorization.user.validate.utils

# Metadata
metadata := {
    "policy_id": "0465",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0465_allowed if {
    data.policies.access.enabled
}
default policy_0465_allowed = false
policy_0465_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0465_allowed if {
    input.user.role == "admin"
}
