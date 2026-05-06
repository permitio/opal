package audit.authorization.resource.check.policy_0880

# Auto-generated policy 880 (Rego v1 syntax)
# Package: audit.authorization.resource.check

# Metadata
metadata := {
    "policy_id": "0880",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default policy_0880_allowed = false
policy_0880_allowed if {
    data.policies.audit.enabled
}
