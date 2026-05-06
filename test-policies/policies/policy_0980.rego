package risk.monitoring.context.validate.core.policy_0980

# Auto-generated policy 980 (Rego v1 syntax)
# Package: risk.monitoring.context.validate.core

# Metadata
metadata := {
    "policy_id": "0980",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0980_allowed if {
    data.policies.risk.enabled
}
default policy_0980_allowed = false
