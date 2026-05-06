package security.monitoring.user.verify.policy_0497

# Auto-generated policy 497 (Rego v1 syntax)
# Package: security.monitoring.user.verify

# Metadata
metadata := {
    "policy_id": "0497",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0497_allowed if {
    input.user.active
    input.resource.public
}
policy_0497_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
policy_0497_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
