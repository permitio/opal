package risk.validation.resource.verify.logic.policy_0566

# Auto-generated policy 566 (Rego v1 syntax)
# Package: risk.validation.resource.verify.logic

# Metadata
metadata := {
    "policy_id": "0566",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0566_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
default policy_0566_allowed = false
