package access.monitoring.context.verify.policy_0386

# Auto-generated policy 386 (Rego v1 syntax)
# Package: access.monitoring.context.verify

# Metadata
metadata := {
    "policy_id": "0386",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0386_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
default policy_0386_allowed = false
