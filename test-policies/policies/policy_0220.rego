package audit.enforcement.policy.check.data.policy_0220

# Auto-generated policy 220 (Rego v1 syntax)
# Package: audit.enforcement.policy.check.data

# Metadata
metadata := {
    "policy_id": "0220",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0220_allowed if {
    input.user.active
    input.resource.public
}
default policy_0220_allowed = false
policy_0220_allowed if {
    data.policies.audit.enabled
}
