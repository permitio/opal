package risk.monitoring.user.validate.policy_0896

# Auto-generated policy 896 (Rego v1 syntax)
# Package: risk.monitoring.user.validate

# Metadata
metadata := {
    "policy_id": "0896",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0896_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0896_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
