import logging
import jwt

from datetime import datetime, timedelta, timezone

from aries_cloudagent.config.wallet import wallet_config
from aries_cloudagent.config.injection_context import InjectionContext
from aries_cloudagent.core.profile import Profile
from aries_cloudagent.wallet.models.wallet_record import WalletRecord
from aries_cloudagent.multitenant.base import BaseMultitenantManager, MultitenantManagerError
from aries_cloudagent.multitenant.manager import MultitenantManager
from aries_cloudagent.multitenant.askar_profile_manager import AskarProfileMultitenantManager

from aries_cloudagent.askar.profile import AskarProfile

from .models import TokensWalletRecord, TokensWalletRecordSchema


class MulittokenHandler:
    def __init__(self, manager: MultitenantManager):
        self.manager = manager
        self.logger = logging.getLogger(__class__.__name__)

    def get_profile(self):
        return self.manager._profile

    async def create_auth_token(
        self, wallet_record: WalletRecord, wallet_key: str = None) -> str:
        self.logger.info('> create_auth_token')
        async with self.get_profile().session() as session:
            tokens_wallet_record = await TokensWalletRecord.retrieve_by_id(session, wallet_record.wallet_id)
            self.logger.debug(tokens_wallet_record)

        iat = datetime.now(tz=timezone.utc)
        # TODO: configuration for how long token is valid.
        exp = iat + timedelta(days=1)

        jwt_payload = {"wallet_id": wallet_record.wallet_id, "iat": iat, "exp": exp}
        jwt_secret = self.get_profile().settings.get("multitenant.jwt_secret")

        if tokens_wallet_record.requires_external_key:
            if not wallet_key:
                raise WalletKeyMissingError()

            jwt_payload["wallet_key"] = wallet_key

        encoded = jwt.encode(jwt_payload, jwt_secret, algorithm="HS256")
        decoded = jwt.decode(encoded, jwt_secret, algorithms=["HS256"])
        # the token we return is the encoded string...
        token = encoded

        # Store this iat as the "valid" singular one in the old multitenant world
        tokens_wallet_record.jwt_iat = decoded.get("iat")
        # add this to the list of issued claims in the multi-token data
        tokens_wallet_record.add_issued_at_claims(decoded.get("iat"))

        # save it...
        async with self.get_profile().session() as session:
            await tokens_wallet_record.save(session)

        # return this token...    
        self.logger.debug(tokens_wallet_record)
        self.logger.info('< create_auth_token')
        return token

    async def get_profile_for_token(
            self, context: InjectionContext, token: str) -> Profile:
        self.logger.info('> get_profile_for_token')

        jwt_secret = self.get_profile().context.settings.get("multitenant.jwt_secret")
        extra_settings = {}

        try:
            token_body = jwt.decode(token, jwt_secret, algorithms=["HS256"])
        except jwt.exceptions.ExpiredSignatureError as err:
            # if exp has expired, we end up here.
            self.logger.error("Expired Signature... clean up claims")
            # ignore expiry so we can get the iat...
            token_body = jwt.decode(token, jwt_secret, algorithms=["HS256"], options={"verify_exp": False})
            wallet_id = token_body.get("wallet_id")
            iat = token_body.get("iat")
            async with self.get_profile().session() as session:
                wallet = await TokensWalletRecord.retrieve_by_id(session, wallet_id)
                wallet.issued_at_claims.remove(iat)
                await wallet.save(session)
            
            async with self.get_profile().session() as session:
                wallet = await TokensWalletRecord.retrieve_by_id(session, wallet_id)

            raise err

        wallet_id = token_body.get("wallet_id")
        wallet_key = token_body.get("wallet_key")
        iat = token_body.get("iat")

        async with self.get_profile().session() as session:
            wallet = await TokensWalletRecord.retrieve_by_id(session, wallet_id)

        if wallet.requires_external_key:
            if not wallet_key:
                raise WalletKeyMissingError()

            extra_settings["wallet.key"] = wallet_key

        # if we are here,      
        token_valid = False    
        for claim in wallet.issued_at_claims:
            if claim == iat:
                token_valid = True

        if not token_valid:
            raise MultitenantManagerError("Token not valid")

        profile = await self.manager.get_wallet_profile(context, wallet, extra_settings)

        self.logger.info('< get_profile_for_token')
        return profile


class BasicMultitokenMultitenantManager(MultitenantManager):

    def __init__(self, profile: Profile):
        super().__init__(profile)
        self.logger = logging.getLogger(__class__.__name__)

    async def create_auth_token(
        self, wallet_record: WalletRecord, wallet_key: str = None) -> str:
        self.logger.info('> create_auth_token')
        handler = MulittokenHandler(self)
        token = await handler.create_auth_token(wallet_record, wallet_key)
        self.logger.info('< create_auth_token')
        return token

    async def get_profile_for_token(
            self, context: InjectionContext, token: str) -> Profile:
        self.logger.info('> get_profile_for_token')
        handler = MulittokenHandler(self)
        profile = await handler.get_profile_for_token(context, token)
        self.logger.info('< get_profile_for_token')
        return profile

class AskarMultitokenMultitenantManager(AskarProfileMultitenantManager):

    def __init__(self, profile: Profile, multitenant_profile: AskarProfile = None):
        super().__init__(profile, multitenant_profile)
        self.logger = logging.getLogger(__class__.__name__)

    async def create_auth_token(
        self, wallet_record: WalletRecord, wallet_key: str = None) -> str:
        self.logger.info('> create_auth_token')
        handler = MulittokenHandler(self)
        token = await handler.create_auth_token(wallet_record, wallet_key)
        self.logger.info('< create_auth_token')
        return token

    async def get_profile_for_token(
            self, context: InjectionContext, token: str) -> Profile:
        self.logger.info('> get_profile_for_token')
        handler = MulittokenHandler(self)
        profile = await handler.get_profile_for_token(context, token)
        self.logger.info('< get_profile_for_token')
        return profile