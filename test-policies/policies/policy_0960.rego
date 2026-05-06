package compliance.authorization.policy.check.core.policy_0960

# Auto-generated policy 960 (Rego v1 syntax)
# Package: compliance.authorization.policy.check.core

# Metadata
metadata := {
    "policy_id": "0960",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0960_allowed if {
    data.policies.compliance.enabled
}
default policy_0960_allowed = false
