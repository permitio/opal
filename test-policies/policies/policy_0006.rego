package risk.authentication.resource.deny.policy_0006

# Auto-generated policy 6 (Rego v1 syntax)
# Package: risk.authentication.resource.deny

# Metadata
metadata := {
    "policy_id": "0006",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0006_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
default policy_0006_allowed = false
