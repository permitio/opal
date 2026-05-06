package risk.authentication.context.allow.helpers.policy_0557

# Auto-generated policy 557 (Rego v1 syntax)
# Package: risk.authentication.context.allow.helpers

# Metadata
metadata := {
    "policy_id": "0557",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0557_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0557_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
policy_0557_allowed if {
    data.policies.risk.enabled
}
