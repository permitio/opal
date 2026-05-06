package governance.authentication.action.verify.policy_0977

# Auto-generated policy 977 (Rego v1 syntax)
# Package: governance.authentication.action.verify

# Metadata
metadata := {
    "policy_id": "0977",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0977_allowed if {
    input.user.role == "admin"
}
default policy_0977_allowed = false
policy_0977_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
