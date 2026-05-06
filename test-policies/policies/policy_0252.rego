package compliance.enforcement.action.validate.data.policy_0252

# Auto-generated policy 252 (Rego v1 syntax)
# Package: compliance.enforcement.action.validate.data

# Metadata
metadata := {
    "policy_id": "0252",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default policy_0252_allowed = false
policy_0252_allowed if {
    input.user.active
    input.resource.public
}
