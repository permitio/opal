package access.enforcement.policy.allow.policy_0008

# Auto-generated policy 8 (Rego v1 syntax)
# Package: access.enforcement.policy.allow

# Metadata
metadata := {
    "policy_id": "0008",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0008_allowed if {
    input.user.active
    input.resource.public
}
policy_0008_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
