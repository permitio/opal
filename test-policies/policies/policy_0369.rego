package risk.authorization.policy.check.policy_0369

# Auto-generated policy 369 (Rego v1 syntax)
# Package: risk.authorization.policy.check

# Metadata
metadata := {
    "policy_id": "0369",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0369_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
policy_0369_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0369_allowed if {
    input.user.role == "admin"
}
