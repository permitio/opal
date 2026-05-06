package access.monitoring.resource.validate.policy_0290

# Auto-generated policy 290 (Rego v1 syntax)
# Package: access.monitoring.resource.validate

# Metadata
metadata := {
    "policy_id": "0290",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default policy_0290_allowed = false
policy_0290_allowed if {
    data.policies.access.enabled
}
