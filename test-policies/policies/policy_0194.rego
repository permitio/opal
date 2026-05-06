package audit.authorization.context.deny.helpers.policy_0194

# Auto-generated policy 194 (Rego v1 syntax)
# Package: audit.authorization.context.deny.helpers

# Metadata
metadata := {
    "policy_id": "0194",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0194_allowed if {
    data.policies.audit.enabled
}
policy_0194_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
policy_0194_allowed if {
    input.user.role == "admin"
}
