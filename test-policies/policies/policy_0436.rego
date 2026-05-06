package compliance.monitoring.context.allow.policy_0436

# Auto-generated policy 436 (Rego v1 syntax)
# Package: compliance.monitoring.context.allow

# Metadata
metadata := {
    "policy_id": "0436",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0436_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
default policy_0436_allowed = false
policy_0436_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
