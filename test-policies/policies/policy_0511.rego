package governance.enforcement.action.deny.helpers.policy_0511

# Auto-generated policy 511 (Rego v1 syntax)
# Package: governance.enforcement.action.deny.helpers

# Metadata
metadata := {
    "policy_id": "0511",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default policy_0511_allowed = false
policy_0511_allowed if {
    input.user.role == "admin"
}
