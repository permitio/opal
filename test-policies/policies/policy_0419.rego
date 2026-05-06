package governance.authentication.user.deny.utils.policy_0419

# Auto-generated policy 419 (Rego v1 syntax)
# Package: governance.authentication.user.deny.utils

# Metadata
metadata := {
    "policy_id": "0419",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default policy_0419_allowed = false
policy_0419_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0419_allowed if {
    input.user.role == "admin"
}
