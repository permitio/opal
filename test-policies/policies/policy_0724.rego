package access.validation.user.allow.policy_0724

# Auto-generated policy 724 (Rego v1 syntax)
# Package: access.validation.user.allow

# Metadata
metadata := {
    "policy_id": "0724",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0724_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
policy_0724_allowed if {
    data.policies.access.enabled
}
policy_0724_allowed if {
    input.user.active
    input.resource.public
}
default policy_0724_allowed = false
