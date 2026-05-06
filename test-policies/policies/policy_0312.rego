package compliance.enforcement.context.validate.policy_0312

# Auto-generated policy 312 (Rego v1 syntax)
# Package: compliance.enforcement.context.validate

# Metadata
metadata := {
    "policy_id": "0312",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default policy_0312_allowed = false
policy_0312_allowed if {
    data.policies.compliance.enabled
}
