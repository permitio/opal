package risk.validation.policy.allow.data.policy_0515

# Auto-generated policy 515 (Rego v1 syntax)
# Package: risk.validation.policy.allow.data

# Metadata
metadata := {
    "policy_id": "0515",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0515_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0515_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
