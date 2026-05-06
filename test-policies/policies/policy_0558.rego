package risk.validation.policy.verify.policy_0558

# Auto-generated policy 558 (Rego v1 syntax)
# Package: risk.validation.policy.verify

# Metadata
metadata := {
    "policy_id": "0558",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0558_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
policy_0558_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
