package governance.validation.context.allow.policy_0351

# Auto-generated policy 351 (Rego v1 syntax)
# Package: governance.validation.context.allow

# Metadata
metadata := {
    "policy_id": "0351",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default policy_0351_allowed = false
policy_0351_allowed if {
    data.policies.governance.enabled
}
