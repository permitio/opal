package security.monitoring.user.verify.policy_0662

# Auto-generated policy 662 (Rego v1 syntax)
# Package: security.monitoring.user.verify

# Metadata
metadata := {
    "policy_id": "0662",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0662_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
policy_0662_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
