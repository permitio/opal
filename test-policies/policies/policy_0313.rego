package risk.validation.action.allow.logic.policy_0313

# Auto-generated policy 313 (Rego v1 syntax)
# Package: risk.validation.action.allow.logic

# Metadata
metadata := {
    "policy_id": "0313",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0313_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
policy_0313_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0313_allowed if {
    data.policies.risk.enabled
}
