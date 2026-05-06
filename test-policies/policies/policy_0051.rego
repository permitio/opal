package compliance.authorization.action.check.policy_0051

# Auto-generated policy 51 (Rego v1 syntax)
# Package: compliance.authorization.action.check

# Metadata
metadata := {
    "policy_id": "0051",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0051_allowed if {
    input.user.active
    input.resource.public
}
policy_0051_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
