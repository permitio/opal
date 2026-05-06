package security.monitoring.policy.verify.data.policy_0096

# Auto-generated policy 96 (Rego v1 syntax)
# Package: security.monitoring.policy.verify.data

# Metadata
metadata := {
    "policy_id": "0096",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0096_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
default policy_0096_allowed = false
policy_0096_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
