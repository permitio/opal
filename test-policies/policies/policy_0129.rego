package governance.validation.user.validate.policy_0129

# Auto-generated policy 129 (Rego v1 syntax)
# Package: governance.validation.user.validate

# Metadata
metadata := {
    "policy_id": "0129",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default policy_0129_allowed = false
policy_0129_allowed if {
    input.user.role == "admin"
}
policy_0129_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
