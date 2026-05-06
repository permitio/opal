package audit.enforcement.action.allow.data.policy_0931

# Auto-generated policy 931 (Rego v1 syntax)
# Package: audit.enforcement.action.allow.data

# Metadata
metadata := {
    "policy_id": "0931",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0931_allowed if {
    input.user.active
    input.resource.public
}
default policy_0931_allowed = false
policy_0931_allowed if {
    data.policies.audit.enabled
}
policy_0931_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
