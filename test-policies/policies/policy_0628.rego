package compliance.validation.action.deny.helpers.policy_0628

# Auto-generated policy 628 (Rego v1 syntax)
# Package: compliance.validation.action.deny.helpers

# Metadata
metadata := {
    "policy_id": "0628",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0628_allowed if {
    input.user.role == "admin"
}
default policy_0628_allowed = false
