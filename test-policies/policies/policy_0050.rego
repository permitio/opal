package compliance.authorization.context.allow.policy_0050

# Auto-generated policy 50 (Rego v1 syntax)
# Package: compliance.authorization.context.allow

# Metadata
metadata := {
    "policy_id": "0050",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0050_allowed if {
    input.user.active
    input.resource.public
}
default policy_0050_allowed = false
