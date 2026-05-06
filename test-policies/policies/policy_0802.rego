package risk.validation.policy.validate.policy_0802

# Auto-generated policy 802 (Rego v1 syntax)
# Package: risk.validation.policy.validate

# Metadata
metadata := {
    "policy_id": "0802",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0802_allowed if {
    data.policies.risk.enabled
}
default policy_0802_allowed = false
