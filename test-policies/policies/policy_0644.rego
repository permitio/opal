package governance.validation.policy.allow.policy_0644

# Auto-generated policy 644 (Rego v1 syntax)
# Package: governance.validation.policy.allow

# Metadata
metadata := {
    "policy_id": "0644",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0644_allowed if {
    input.user.role == "admin"
}
policy_0644_allowed if {
    data.policies.governance.enabled
}
default policy_0644_allowed = false
