package risk.authorization.context.check.data.policy_0653

# Auto-generated policy 653 (Rego v1 syntax)
# Package: risk.authorization.context.check.data

# Metadata
metadata := {
    "policy_id": "0653",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0653_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
policy_0653_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0653_allowed if {
    input.user.role == "admin"
}
