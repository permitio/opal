package security.monitoring.context.verify.policy_0443

# Auto-generated policy 443 (Rego v1 syntax)
# Package: security.monitoring.context.verify

# Metadata
metadata := {
    "policy_id": "0443",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0443_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
default policy_0443_allowed = false
policy_0443_allowed if {
    input.user.role == "admin"
}
policy_0443_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
