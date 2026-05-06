package compliance.enforcement.action.allow.data.policy_0953

# Auto-generated policy 953 (Rego v1 syntax)
# Package: compliance.enforcement.action.allow.data

# Metadata
metadata := {
    "policy_id": "0953",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default policy_0953_allowed = false
policy_0953_allowed if {
    data.policies.compliance.enabled
}
