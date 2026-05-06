package risk.validation.context.deny.policy_0181

# Auto-generated policy 181 (Rego v1 syntax)
# Package: risk.validation.context.deny

# Metadata
metadata := {
    "policy_id": "0181",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0181_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0181_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
policy_0181_allowed if {
    data.policies.risk.enabled
}
