package audit.validation.resource.check.policy_0970

# Auto-generated policy 970 (Rego v1 syntax)
# Package: audit.validation.resource.check

# Metadata
metadata := {
    "policy_id": "0970",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default policy_0970_allowed = false
policy_0970_allowed if {
    input.user.active
    input.resource.public
}
