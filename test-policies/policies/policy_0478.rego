package risk.authentication.context.check.policy_0478

# Auto-generated policy 478 (Rego v1 syntax)
# Package: risk.authentication.context.check

# Metadata
metadata := {
    "policy_id": "0478",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0478_allowed if {
    data.policies.risk.enabled
}
policy_0478_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0478_allowed if {
    input.user.role == "admin"
}
policy_0478_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
