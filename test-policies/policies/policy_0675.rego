package compliance.validation.action.deny.policy_0675

# Auto-generated policy 675 (Rego v1 syntax)
# Package: compliance.validation.action.deny

# Metadata
metadata := {
    "policy_id": "0675",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default policy_0675_allowed = false
policy_0675_allowed if {
    input.user.active
    input.resource.public
}
