package compliance.enforcement.resource.allow.policy_0215

# Auto-generated policy 215 (Rego v1 syntax)
# Package: compliance.enforcement.resource.allow

# Metadata
metadata := {
    "policy_id": "0215",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0215_allowed if {
    data.policies.compliance.enabled
}
default policy_0215_allowed = false
policy_0215_allowed if {
    input.user.role == "admin"
}
