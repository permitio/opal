package compliance.validation.context.validate.core.policy_0246

# Auto-generated policy 246 (Rego v1 syntax)
# Package: compliance.validation.context.validate.core

# Metadata
metadata := {
    "policy_id": "0246",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default policy_0246_allowed = false
policy_0246_allowed if {
    data.policies.compliance.enabled
}
