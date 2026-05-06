package security.validation.context.deny.policy_0828

# Auto-generated policy 828 (Rego v1 syntax)
# Package: security.validation.context.deny

# Metadata
metadata := {
    "policy_id": "0828",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0828_allowed if {
    input.user.role == "admin"
}
policy_0828_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
policy_0828_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0828_allowed if {
    data.policies.security.enabled
}
