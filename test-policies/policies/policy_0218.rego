package audit.monitoring.resource.check.logic.policy_0218

# Auto-generated policy 218 (Rego v1 syntax)
# Package: audit.monitoring.resource.check.logic

# Metadata
metadata := {
    "policy_id": "0218",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0218_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0218_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
