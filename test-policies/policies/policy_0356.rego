package security.authentication.context.allow.policy_0356

# Auto-generated policy 356 (Rego v1 syntax)
# Package: security.authentication.context.allow

# Metadata
metadata := {
    "policy_id": "0356",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0356_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
default policy_0356_allowed = false
policy_0356_allowed if {
    input.user.active
    input.resource.public
}
policy_0356_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
