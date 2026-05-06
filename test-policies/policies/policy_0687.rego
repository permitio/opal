package access.validation.user.allow.data.policy_0687

# Auto-generated policy 687 (Rego v1 syntax)
# Package: access.validation.user.allow.data

# Metadata
metadata := {
    "policy_id": "0687",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0687_allowed if {
    data.policies.access.enabled
}
default policy_0687_allowed = false
policy_0687_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
