package access.enforcement.action.check.data.policy_0556

# Auto-generated policy 556 (Rego v1 syntax)
# Package: access.enforcement.action.check.data

# Metadata
metadata := {
    "policy_id": "0556",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0556_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
default policy_0556_allowed = false
policy_0556_allowed if {
    input.user.role == "admin"
}
