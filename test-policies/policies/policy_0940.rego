package security.monitoring.resource.validate.utils.policy_0940

# Auto-generated policy 940 (Rego v1 syntax)
# Package: security.monitoring.resource.validate.utils

# Metadata
metadata := {
    "policy_id": "0940",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default policy_0940_allowed = false
policy_0940_allowed if {
    data.policies.security.enabled
}
policy_0940_allowed if {
    input.user.role == "admin"
}
