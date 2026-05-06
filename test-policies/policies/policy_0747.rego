package access.enforcement.context.verify.policy_0747

# Auto-generated policy 747 (Rego v1 syntax)
# Package: access.enforcement.context.verify

# Metadata
metadata := {
    "policy_id": "0747",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0747_allowed if {
    input.user.active
    input.resource.public
}
policy_0747_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
